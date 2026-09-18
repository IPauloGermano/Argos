import os
import pytest
import docx
from app.services.resume import (
    validate_upload,
    extract_text_from_upload,
    deterministic_parse_resume,
    segment_resume,
    _extract_skills,
    _extract_languages,
    _extract_experience_and_seniority,
    _extract_headline_and_roles,
    _extract_summary
)

def test_resume_model_academic_intern():
    """Modelo 1: Estudante / Acadêmico buscando Estágio (sem emprego formal anterior)."""
    cv = """
    Lucas Santos
    Recife, PE • lucas@email.com • github.com/lucassantos
    Estudante de Análise e Desenvolvimento de Sistemas

    Objetivo:
    Estágio em Desenvolvimento de Software ou Estágio em TI

    Resumo Profissional:
    Estudante de ADS com projetos práticos em Python, Django e desenvolvimento de APIs REST.
    Vivência com modelagem de bancos de dados relacionais em SQLite e PostgreSQL, uso de Git e Docker.

    Educação:
    Faculdade de Tecnologia - Cursando (Previsão de formatura: 2026)

    Projetos:
    - Sistema de Gestão Web: Desenvolvido com Django, Django ORM, HTML5 e Bootstrap.
    - API de Catálogo: Construída em FastAPI e PostgreSQL com testes automatizados via Pytest.

    Conhecimentos Técnicos:
    Linguagens e Frameworks: Python, Django, FastAPI, SQL, SQLite, PostgreSQL
    Ferramentas e Infra: Git, GitHub, Linux, Docker, Prompt Engineering
    Testes e Metodologias: Testes Unitários, TDD, Metodologias Ágeis

    Idiomas:
    Inglês (Intermediário - Leitura técnica)
    Português (Nativo)
    """
    parsed = deterministic_parse_resume(cv)
    assert parsed["seniority"] == "junior"
    assert parsed["years_experience"] in (0, 1)
    assert "Python" in parsed["skills"]
    assert "Django" in parsed["skills"]
    assert "FastAPI" in parsed["skills"]
    assert "Docker" in parsed["skills"]
    assert "Git" in parsed["skills"]
    assert "PostgreSQL" in parsed["skills"]
    assert any("Estágio" in r or "Júnior" in r for r in parsed["roles"])
    assert "Inglês (Intermediário - Leitura técnica)" in parsed["languages"]
    assert "Português (Nativo)" in parsed["languages"]
    assert "Estudante de ADS" in parsed["summary"]

def test_resume_model_two_column_modern():
    """Modelo 2: Layout moderno de duas colunas (estilo Canva / NovoResume)."""
    cv = """
    Beatriz Rocha
    Curitiba, PR | beatriz@dev.io
    Desenvolvedora Full Stack Pleno

    SOBRE MIM
    Engenheira de software com 3 anos de experiência sólida em React, Node.js, TypeScript e microsserviços.
    Atuação no desenvolvimento de ponta a ponta com foco em performance e qualidade.

    EXPERIÊNCIA PROFISSIONAL
    Fintech Nova (2021 - 2024)
    Desenvolvedora Full Stack
    - Desenvolvimento de interfaces em React, Next.js e Tailwind CSS.
    - Criação de APIs em Node.js com Express e NestJS conectadas a PostgreSQL e Redis.
    - Testes automatizados com Jest e Cypress, pipelines de CI/CD no GitHub Actions.

    HABILIDADES TÉCNICAS
    React, Next.js, Node.js, TypeScript, JavaScript, Tailwind CSS, PostgreSQL, Redis, Docker, CI/CD, Jest

    IDIOMAS
    Inglês Avançado
    Espanhol Intermediário
    Português Nativo
    """
    parsed = deterministic_parse_resume(cv)
    assert parsed["seniority"] == "mid"
    assert parsed["years_experience"] == 3
    assert "React" in parsed["skills"]
    assert "Node.js" in parsed["skills"]
    assert "TypeScript" in parsed["skills"]
    assert "Tailwind CSS" in parsed["skills"]
    assert "Docker" in parsed["skills"]
    assert "Inglês (Avançado)" in parsed["languages"]
    assert "Espanhol (Intermediário)" in parsed["languages"]
    assert "Português (Nativo)" in parsed["languages"]

def test_resume_model_international_english():
    """Modelo 3: Currículo internacional em inglês (US/Europe format, Senior DevOps)."""
    cv = """
    Alexander Wright
    London, United Kingdom | alex.wright@cloudops.org
    Senior Cloud & DevOps Engineer

    SUMMARY
    Senior DevOps and Infrastructure Engineer with 7 years of hands-on experience building scalable AWS environments.
    Expertise in Kubernetes, Terraform, Docker, CI/CD automation, and Linux administration.

    WORK EXPERIENCE
    Lead SRE & DevOps Engineer | SkyTech Ltd (2017 - 2024)
    - Architected Kubernetes clusters (EKS) serving 10M+ daily requests.
    - Automated infrastructure as code with Terraform and Ansible.
    - Built multi-region GitHub Actions pipelines.

    TECHNICAL SKILLS
    AWS, Kubernetes, Docker, Terraform, Ansible, Linux, Python, Go, CI/CD, GitHub Actions

    LANGUAGES
    English (Native)
    Spanish (Fluent)
    """
    parsed = deterministic_parse_resume(cv)
    assert parsed["seniority"] == "senior"
    assert parsed["years_experience"] >= 5
    assert "AWS" in parsed["skills"]
    assert "Kubernetes" in parsed["skills"]
    assert "Terraform" in parsed["skills"]
    assert "Docker" in parsed["skills"]
    assert "Linux" in parsed["skills"]
    assert "English (Fluente)" in parsed["languages"] or "English (Native)" in parsed["languages"] or any("Inglês" in l for l in parsed["languages"])

def test_resume_docx_with_tables_and_textboxes(tmp_path):
    """Modelo 4: Documento DOCX com tabelas e caixas de texto."""
    doc_path = tmp_path / "resume_template.docx"
    doc = docx.Document()
    
    # Cabeçalho
    doc.add_paragraph("Carlos Eduardo Silva")
    doc.add_paragraph("Desenvolvedor Python Júnior | Django | APIs REST")

    # Tabela de duas colunas (comum em templates Word)
    table = doc.add_table(rows=1, cols=2)
    left_cell = table.cell(0, 0)
    left_cell.text = "Resumo Profissional:\nDesenvolvedor backend focado em Python e APIs REST."
    
    right_cell = table.cell(0, 1)
    right_cell.text = "Conhecimentos Técnicos:\nPython, Django, FastAPI, Docker, SQL, Git"

    doc.save(str(doc_path))

    # Extração de texto e validação
    extracted_text = extract_text_from_upload(str(doc_path), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert "Python" in extracted_text
    assert "Django" in extracted_text

    parsed = deterministic_parse_resume(extracted_text)
    assert "Python" in parsed["skills"]
    assert "Django" in parsed["skills"]
    assert "FastAPI" in parsed["skills"]
    assert "Docker" in parsed["skills"]

def test_resume_rtf_and_markdown_support(tmp_path):
    """Modelo 5: Suporte a arquivos RTF e Markdown."""
    # 1. RTF
    rtf_path = tmp_path / "curriculo.rtf"
    rtf_content = r"{\rtf1\ansi\deff0 {\fonttbl {\f0 Arial;}}\f0\fs24 Mariana Souza \par Desenvolvedora Backend Python \par Habilidades: Python, Flask, Docker.}"
    rtf_path.write_text(rtf_content, encoding="utf-8")

    validate_upload("curriculo.rtf", "application/rtf", os.path.getsize(str(rtf_path)))
    rtf_text = extract_text_from_upload(str(rtf_path), "application/rtf")
    assert "Python" in rtf_text
    parsed_rtf = deterministic_parse_resume(rtf_text)
    assert "Python" in parsed_rtf["skills"]

    # 2. Markdown (.md)
    md_path = tmp_path / "resume.md"
    md_content = """# João Silva
## Desenvolvedor de Software Júnior
### Resumo
Desenvolvedor com experiência em Python, Django e PostgreSQL.
### Habilidades
- Python
- Django
- PostgreSQL
- Docker
"""
    md_path.write_text(md_content, encoding="utf-8")
    validate_upload("resume.md", "text/markdown", os.path.getsize(str(md_path)))
    md_text = extract_text_from_upload(str(md_path), "text/markdown")
    parsed_md = deterministic_parse_resume(md_text)
    assert "Python" in parsed_md["skills"]
    assert "Django" in parsed_md["skills"]
    assert "PostgreSQL" in parsed_md["skills"]

def test_language_intermediate_does_not_inflate_seniority():
    """Garante que 'Inglês Intermediário' não faz a senioridade do candidato virar Pleno/Mid erroneamente."""
    cv = """
    Estudante Estagiário
    Resumo:
    Estudante buscando primeira oportunidade como Desenvolvedor Júnior.
    Idiomas:
    Inglês Intermediário
    Português Nativo
    """
    parsed = deterministic_parse_resume(cv)
    assert parsed["seniority"] == "junior"
    assert parsed["seniority"] != "mid"
