import type { TranslationKey } from '@/i18n/translations';

// O nome e a moeda do modelo semântico vêm do backend (GET /model, useModelInfo).
export const ACTIVE_CLIENT = {
  name: 'Power BI',
  adapter: 'fabric',
  dataset: 'semantic_model',
} as const;

export type Adapter = typeof ACTIVE_CLIENT.adapter;

export interface ModuleConfig {
  id: string;
  nameKey: TranslationKey;
  placeholderKey: TranslationKey;
  source?: string;
  hero: {
    titleKey: TranslationKey;
    subtitleKey: TranslationKey;
  };
  suggestionKeys: TranslationKey[];
}

export const MODULE_CONFIG: ModuleConfig = {
  id: 'fabric',
  nameKey: 'module.fabric.name',
  placeholderKey: 'module.fabric.placeholder',
  source: 'Power BI',
  hero: {
    titleKey: 'module.fabric.hero.title',
    subtitleKey: 'module.fabric.hero.subtitle',
  },
  suggestionKeys: [],
};
