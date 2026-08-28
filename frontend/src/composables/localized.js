import {useI18n} from 'vue-i18n';

// The API sends both languages (`name_en` / `name_ru`); pick by the active locale with an
// English fallback, mirroring modeltranslation's fallback on the server.
export function useLocalized() {
    const {locale} = useI18n();
    return (obj, field = 'name') => obj?.[`${field}_${locale.value}`] || obj?.[`${field}_en`] || '';
}
