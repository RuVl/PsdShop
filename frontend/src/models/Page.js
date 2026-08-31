import Localized from '@/models/Localized.js';

// An owner-written text page (content.Page). `body` is HTML from the admin editor.
export default class Page extends Localized {
    static translated = ['title', 'body'];
}

Page.defineTranslations();
