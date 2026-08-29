import Localized from '@/models/Localized.js';

// The settings singleton behind the footer.
export default class SiteSettings extends Localized {
    static translated = ['footer_note'];
}

SiteSettings.defineTranslations();
