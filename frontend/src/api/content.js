import api from '@/api/index.js';

// Owner-written content, mirroring the bot pages: pages, slides, site-wide settings.

export async function fetchPages() {
    return (await api.get('/content/pages/')).data;
}

export async function fetchPage(slug) {
    return (await api.get(`/content/pages/${slug}/`)).data;
}

export async function fetchSlides() {
    return (await api.get('/content/slides/')).data;
}

export async function fetchSettings() {
    return (await api.get('/content/settings/')).data;
}
