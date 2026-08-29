import Localized from '@/models/Localized.js';

// One welcome slide from the admin.
export default class Slide extends Localized {
    static translated = ['title', 'text', 'button_label'];

    get hasButton() {
        return Boolean(this.button_label && this.button_url);
    }
}

Slide.defineTranslations();
