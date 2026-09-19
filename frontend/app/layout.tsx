import type { Metadata } from "next";
import Nav from "../components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Argos Job Hunter 2.0 • Assistente Pessoal de Vagas",
  description: "Seu concierge autônomo de busca de empregos e oportunidades de carreira personalizadas.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen bg-surface-base text-zinc-100 antialiased selection:bg-brand-500 selection:text-black">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-5 sm:py-8">
          {/* Header Superior Limpo & Autoral */}
          <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-5 mb-5 border-b border-surface-border">
            <div>
              <div className="flex items-center gap-2.5">
                <span className="text-amber-400 text-xl" aria-hidden="true">✦</span>
                <span className="text-xl font-bold tracking-tight text-white font-serif">
                  Argos
                </span>
                <span className="text-xs text-zinc-400 font-medium px-2 py-0.5 rounded bg-surface-card border border-surface-border">
                  Job Hunter 2.0
                </span>
              </div>
              <p className="text-xs text-zinc-400 mt-1 max-w-prose">
                Seu assistente pessoal de carreira: filtrando o mercado para encontrar o que realmente importa.
              </p>
            </div>

            <div className="flex items-center gap-2 self-start sm:self-center">
              <div
                className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface-card border border-surface-border text-xs text-zinc-300 shadow-sm"
                role="status"
                aria-label="Status do assistente: Monitoramento contínuo ativo"
              >
                <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true"></span>
                <span className="font-medium text-xs">Monitoramento ativo</span>
              </div>
            </div>
          </header>

          {/* Navegação Principal */}
          <Nav />

          {/* Conteúdo Central */}
          <main id="main-content">{children}</main>

          {/* Rodapé Sóbrio */}
          <footer className="mt-16 pt-6 border-t border-surface-border text-center text-xs text-zinc-400 flex flex-col sm:flex-row sm:justify-between gap-2">
            <p>Argos Job Hunter 2.0 • Curadoria Pessoal de Carreira</p>
            <p className="text-zinc-400">Você no controle total das suas candidaturas</p>
          </footer>
        </div>
      </body>
    </html>
  );
}
