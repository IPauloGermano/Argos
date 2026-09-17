from __future__ import annotations
import os
import re
from typing import Optional


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
ALLOWED_MIMETYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
    "text/x-python",
    "application/octet-stream"  # alguns clientes enviam binários como octet-stream
}


def validate_upload(filename: str, content_type: str, size: int, max_mb: int = 10) -> None:
    """Valida tamanho, presença de dados e formato do arquivo de currículo."""
    if size == 0:
        raise ValueError("Arquivo vazio")
    
    if size > max_mb * 1024 * 1024:
        raise ValueError(f"Arquivo maior que {max_mb}MB")

    ext = os.path.splitext(filename.lower())[1] if filename else ""
    if ext:
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Formato não suportado ('{ext}'). Envie arquivos PDF, DOCX ou TXT")
    elif content_type not in ALLOWED_MIMETYPES:
        raise ValueError(f"Formato não suportado ('{content_type}'). Envie arquivos PDF, DOCX ou TXT")


def extract_text_from_pdf(path: str) -> str:
    """Extrai texto de arquivo PDF utilizando pypdf com detecção de corrupção."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(path)
        if len(reader.pages) == 0:
            raise ValueError("O arquivo PDF não contém páginas")
        parts = [(page.extract_text() or "") for page in reader.pages]
        text = "\n".join(parts).strip()
        if not text:
            raise ValueError("O arquivo PDF não contém texto legível")
        return text
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Arquivo PDF corrompido ou ilegível: {e}")


def extract_text_from_docx(path: str) -> str:
    """Extrai texto de arquivo DOCX utilizando python-docx com detecção de corrupção."""
    try:
        import docx
        doc = docx.Document(path)
        parts = []
        for p in doc.paragraphs:
            if p.text.strip():
                parts.append(p.text.strip())
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    parts.append(row_text)
        text = "\n".join(parts).strip()
        if not text:
            raise ValueError("O documento DOCX não contém texto legível")
        return text
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Arquivo DOCX corrompido ou ilegível: {e}")


def extract_text_from_txt(path: str) -> str:
    """Extrai texto de arquivo TXT suportando codificações UTF-8 e Latin-1."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1", errors="replace") as f:
            text = f.read().strip()
    except Exception as e:
        raise ValueError(f"Erro ao ler arquivo TXT: {e}")

    if not text:
        raise ValueError("O arquivo TXT está vazio")
    return text


def extract_text_from_upload(path: str, content_type: str = "") -> str:
    """Ponto único de extração de texto para currículos (PDF, DOCX, TXT)."""
    ext = os.path.splitext(path.lower())[1]

    if ext == ".pdf" or "pdf" in content_type.lower():
        return extract_text_from_pdf(path)
    elif ext == ".docx" or "word" in content_type.lower() or "document" in content_type.lower():
        return extract_text_from_docx(path)
    elif ext == ".txt" or "plain" in content_type.lower():
        return extract_text_from_txt(path)
    else:
        # Tenta detectar magicamente pelo cabeçalho
        with open(path, "rb") as f:
            head = f.read(8)
        if head.startswith(b"%PDF"):
            return extract_text_from_pdf(path)
        elif head.startswith(b"PK\x03\x04"):
            return extract_text_from_docx(path)
        else:
            return extract_text_from_txt(path)


def deterministic_parse_resume(text: str) -> dict:
    """
    Parser determinístico e sem alucinação de dados cadastrais essenciais.
    Extrai habilidades e termos explicitamente citados no texto do currículo.
    """
    if not text:
        return {}

    skills_catalog = [
        "python", "django", "fastapi", "flask", "docker", "kubernetes",
        "sql", "postgresql", "mysql", "sqlite", "mongodb", "redis",
        "git", "github", "linux", "rest", "graphql", "aws", "azure", "gcp",
        "javascript", "typescript", "react", "next.js", "node.js", "vue",
        "java", "c#", ".net", "c++", "go", "golang", "rust", "html5", "css3",
        "ci/cd", "testes unitários", "tdd", "scrum", "kanban", "prompt engineering",
        "inteligência artificial", "ia generativa", "machine learning"
    ]

    lower_text = text.lower()
    matched_skills = []
    for sk in skills_catalog:
        pattern = r"\b" + re.escape(sk) + r"\b"
        if re.search(pattern, lower_text):
            # Formata capitalização padrão
            matched_skills.append(sk.title() if len(sk) > 3 else sk.upper())

    # Detecta senioridade
    seniority = "junior"
    if re.search(r"\b(s[eê]nior|sr\.?|lead|especialista|principal)\b", lower_text):
        seniority = "senior"
    elif re.search(r"\b(pleno|pl\.?|mid-level|intermedi[aá]rio)\b", lower_text):
        seniority = "mid"
    elif re.search(r"\b(est[aá]gio|estagi[aá]ri[oa]|trainee|iniciante)\b", lower_text):
        seniority = "junior"

    # Detecta papéis / cargos
    roles = []
    role_patterns = [
        ("desenvolvedor python", "Desenvolvedor Python"),
        ("backend developer", "Desenvolvedor Backend"),
        ("desenvolvedor backend", "Desenvolvedor Backend"),
        ("software engineer", "Engenheiro de Software"),
        ("engenheiro de software", "Engenheiro de Software"),
        ("estágio em desenvolvimento", "Estágio em Desenvolvimento"),
        ("desenvolvedor frontend", "Desenvolvedor Frontend"),
        ("desenvolvedor full stack", "Desenvolvedor Full Stack"),
        ("analista de sistemas", "Analista de Sistemas"),
    ]
    for pattern, label in role_patterns:
        if pattern in lower_text:
            roles.append(label)

    if not roles:
        roles = ["Desenvolvedor de Software"]

    return {
        "skills": matched_skills,
        "seniority": seniority,
        "roles": roles,
        "languages": ["Português"] if "português" in lower_text or "portugues" in lower_text or not "english" in lower_text else ["Português", "Inglês"]
    }
