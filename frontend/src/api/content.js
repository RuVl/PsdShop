import api from '@/api/index.js';
import Page from '@/models/Page.js';
import SiteSettings from '@/models/SiteSettings.js';
import Slide from '@/models/Slide.js';

// Owner-written content, mirroring the bot pages: pages, slides, site-wide settings.

export async function fetchPages() {
    const {data} = await api.get('/content/pages/');
    return data.map(item => new Page(item));
}

export async function fetchPage(slug) {
    return new Page((await api.get(`/content/pages/${slug}/`)).data);
}

export async function fetchSlides() {
    const {data} = await api.get('/content/slides/');
    return data.map(item => new Slide(item));
}

export async function fetchSettings() {
    return new SiteSettings((await api.get('/content/settings/')).data);
}
