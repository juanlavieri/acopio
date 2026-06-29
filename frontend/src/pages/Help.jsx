import { useEffect, useState } from "react";
import { HelpCircle, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { useT } from "../lib/i18n.jsx";

export default function Help() {
  const { t, lang } = useT();
  const [sections, setSections] = useState(null);

  useEffect(() => {
    api.get(`/api/help?lang=${lang}`).then((d) => setSections(d.sections)).catch(() => setSections([]));
  }, [lang]);

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{t("help.title")}</h1>
        <p className="text-sm text-slate-500">{t("help.subtitle")}</p>
      </div>

      <div className="flex items-start gap-2 rounded-2xl border border-brand-200 bg-brand-50 p-4 text-sm text-brand-800">
        <Sparkles size={18} className="mt-0.5 shrink-0 text-brand-600" />
        <span>{t("ai.greeting")}</span>
      </div>

      {!sections ? (
        <div className="text-slate-400">{t("common.loading")}</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {sections.map((s, i) => (
            <div key={i} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-2 flex items-center gap-2">
                <span className="grid h-7 w-7 place-items-center rounded-lg bg-brand-50 text-brand-700">
                  <HelpCircle size={16} />
                </span>
                <h3 className="font-semibold text-slate-800">{s.title}</h3>
              </div>
              <ul className="space-y-1.5">
                {s.items.map((it, j) => (
                  <li key={j} className="flex gap-2 text-sm text-slate-600">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-400" />
                    <span>{it}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
