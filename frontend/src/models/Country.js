import Localized from '@/models/Localized.js';

// A country of the catalog: one segment of every listing URL, one row of the sidebar.
export default class Country extends Localized {
    static translated = ['name', 'seo_text'];
}

Country.defineTranslations();
