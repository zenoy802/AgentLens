export type ProductLanguage = "zh-CN" | "en-US";

const PRODUCT_LANGUAGE_STORAGE_KEY = "agentlens.productLanguage";
const PRODUCT_LANGUAGES = new Set<ProductLanguage>(["zh-CN", "en-US"]);

export function isProductLanguage(value: string | null): value is ProductLanguage {
  return value !== null && PRODUCT_LANGUAGES.has(value as ProductLanguage);
}

export function detectProductLanguage(locale?: string): ProductLanguage {
  const resolvedLocale =
    locale ??
    (typeof navigator === "undefined"
      ? undefined
      : navigator.languages[0] ?? navigator.language);

  return resolvedLocale?.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
}

export function loadProductLanguage(): ProductLanguage {
  if (typeof window === "undefined") {
    return detectProductLanguage();
  }

  try {
    const storedLanguage = window.localStorage.getItem(PRODUCT_LANGUAGE_STORAGE_KEY);
    if (isProductLanguage(storedLanguage)) {
      return storedLanguage;
    }
  } catch {
    return detectProductLanguage();
  }

  return detectProductLanguage();
}

export function saveProductLanguage(language: ProductLanguage): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(PRODUCT_LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Local storage can be unavailable in private or locked-down browser contexts.
  }
}
