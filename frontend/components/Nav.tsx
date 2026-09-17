"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Nav() {
  const pathname = usePathname();

  const links = [
    { href: "/", label: "Início", icon: "🏠" },
    { href: "/jobs", label: "Vagas", icon: "💼" },
    { href: "/profile", label: "Meu Perfil", icon: "👤" },
    { href: "/notifications", label: "Alertas", icon: "🔔" },
  ];

  return (
    <nav
      aria-label="Navegação Principal"
      className="flex items-center justify-between p-1 bg-surface-card border border-surface-border rounded-xl mb-6 shadow-sm"
    >
      <div className="flex items-center gap-1 sm:gap-1.5 w-full sm:w-auto" role="tablist">
        {links.map((link) => {
          const isActive =
            pathname === link.href ||
            (link.href !== "/" && pathname.startsWith(link.href));
          return (
            <Link
              key={link.href}
              href={link.href}
              role="tab"
              aria-selected={isActive}
              className={`flex-1 sm:flex-none px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all text-center inline-flex items-center justify-center gap-2 min-h-[44px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 ${
                isActive
                  ? "bg-brand-500 text-white shadow-sm font-semibold"
                  : "text-zinc-400 hover:text-zinc-100 hover:bg-surface-elevated active:bg-surface-subtle"
              }`}
            >
              <span className="text-base" aria-hidden="true">{link.icon}</span>
              <span className="text-xs sm:text-sm">{link.label}</span>
            </Link>
          );
        })}
      </div>

      {/* Atalho discreto para configurações técnicas secundárias */}
      <div className="hidden md:flex items-center pr-2">
        <Link
          href="/preferences"
          className="text-xs text-zinc-400 hover:text-zinc-200 px-3 py-2 rounded-md hover:bg-surface-elevated transition-colors inline-flex items-center gap-1.5 focus-visible:ring-2 focus-visible:ring-brand-400"
          title="Filtros avançados e regras de exclusão"
        >
          <span aria-hidden="true">⚙️</span>
          <span>Avançado</span>
        </Link>
      </div>
    </nav>
  );
}
