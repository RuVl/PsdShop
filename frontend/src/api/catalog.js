import api from '@/api/index.js';
import Country from '@/models/Country.js';
import DocumentType from '@/models/DocumentType.js';
import Product from '@/models/Product.js';

// The catalog API mirrors the bot pages: same querysets, same "unknown slug is a 404" rule.
// Every payload carries both languages, so a language switch never refetches. This module is the
// border between HTTP and the app: what leaves it is a model, never a raw payload.

export async function fetchCountries() {
    const {data} = await api.get('/catalog/countries/');
    return data.map(item => new Country(item));
}

export async function fetchDocumentTypes() {
    const {data} = await api.get('/catalog/document-types/');
    return data.map(item => new DocumentType(item));
}

export async function fetchProducts({country, type, page, q} = {}) {
    const params = {};
    if (country && country !== 'all') params.country = country;
    if (type && type !== 'all') params.type = type;
    if (page && page > 1) params.page = page;
    // The search is the server's: filtering the loaded pages alone would count the pagination
    // against the whole catalog and offer a "load more" that adds nothing to what is shown.
    if (q) params.q = q;

    const {data} = await api.get('/catalog/products/', {params});
    // `total_pages` comes from the server (catalog.views.CatalogPagination): the page size is the
    // API's business, and a copy of it here would silently rot the moment the server changed it.
    return {count: data.count, totalPages: data.total_pages, results: data.results.map(item => new Product(item))};
}

export async function fetchProduct(id) {
    return new Product((await api.get(`/catalog/products/${id}/`)).data);
}
