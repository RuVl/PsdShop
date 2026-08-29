import Localized from '@/models/Localized.js';

// A kind of document - the badge on a card and the second segment of a listing URL.
export default class DocumentType extends Localized {
    static translated = ['name', 'seo_text'];
}

DocumentType.defineTranslations();
