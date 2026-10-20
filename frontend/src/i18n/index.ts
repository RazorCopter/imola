import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import it from "./it.json";

/**
 * L'interfaccia è in italiano. L'inglese esiste come scheletro con le stesse chiavi
 * (en.json, valori vuoti): i18next ricade sull'italiano per ogni chiave non tradotta.
 */
export const defaultNS = "translation";

void i18next.use(initReactI18next).init({
  resources: { it: { translation: it } },
  lng: "it",
  fallbackLng: "it",
  defaultNS,
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18next;
