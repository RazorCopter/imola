import { useTranslation } from "react-i18next";
import { Construction } from "lucide-react";

/** Segnaposto per le sezioni completate nelle fasi successive del piano. */
export function PlaceholderPage({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation();
  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold tracking-tight">{t(titleKey)}</h1>
      <div className="flex items-center gap-3 rounded-lg border border-dashed border-border bg-card p-8 text-sm text-muted-foreground">
        <Construction className="size-5 shrink-0" aria-hidden />
        <p>
          Sezione in costruzione: le fondamenta (modello dati, formule e API delle viste calcolate)
          sono pronte, l&apos;interfaccia arriva nella Fase 3 del piano.
        </p>
      </div>
    </section>
  );
}
