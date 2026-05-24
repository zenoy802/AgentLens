import { create } from "zustand";

import {
  loadProductLanguage,
  saveProductLanguage,
  type ProductLanguage,
} from "@/lib/productLanguage";

interface ProductLanguageState {
  language: ProductLanguage;
  setLanguage(language: ProductLanguage): void;
}

export const useProductLanguageStore = create<ProductLanguageState>((set) => ({
  language: loadProductLanguage(),
  setLanguage: (language) => {
    saveProductLanguage(language);
    set({ language });
  },
}));
