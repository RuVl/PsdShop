import api from '@/api/index.js';

// The catalog API mirrors the bot pages: same querysets, same "unknown slug is a 404" rule.
// Every payload carries both languages, so a language switch never refetches.

export async function fetchCountries() {
    return (await api.get('/catalog/countries/')).data;
}

export async function fetchDocumentTypes() {
    return (await api.get('/catalog/document-types/')).data;
}

export async function fetchProducts({country, type, page} = {}) {
    const params = {};
    if (country && country !== 'all') params.country = country;
    if (type && type !== 'all') params.type = type;
    if (page && page > 1) params.page = page;
    return (await api.get('/catalog/products/', {params})).data;
}

export async function fetchProduct(id) {
    return (await api.get(`/catalog/products/${id}/`)).data;
}
