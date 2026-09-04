import {createRouter, createWebHistory} from 'vue-router';
import {useSettingsStore} from "@/stores/settings.js";
import {SUPPORT_LOCALES} from "@/i18n/index.js";

// The URL space mirrors backend/backend/urlspace.py and the Django routes in
// storefront/urls.py - one address space, two presentations (dynamic rendering).
// The language lives in the path; Django serves the same URLs to bots.
const routes = [
    {
        // The trailing slash is part of the address: Django serves `/en/` and canonicalises to it,
        // so a client-side navigation must not quietly drop it.
        path: `/:lang(${SUPPORT_LOCALES.join('|')})/`,
        children: [
            {
                name: 'home',
                path: '',
                // Two views: the page itself, and the hero App.vue puts inside the dark strip -
                // the SPA half of the `hero` block storefront/catalog.html overrides.
                components: {
                    default: () => import("@/views/Catalog.vue"),
                    hero: () => import("@/components/storefront/HomeHero.vue"),
                },
            },
            {
                name: 'cart',
                path: 'cart/',
                component: () => import("@/views/Cart.vue"),
            },
            {
                name: 'purchases',
                path: 'purchases/',
                component: () => import("@/views/MyPurchases.vue"),
            },
            {
                // The token is the whole authentication - it arrives by e-mail and expires, see docs/architecture.md.
                name: 'purchases-list',
                path: 'purchases/:token/',
                component: () => import("@/views/Purchases.vue"),
            },
            {
                // Reached from an e-mail footer; the token is signed, so the page needs nothing else.
                name: 'unsubscribe',
                path: 'unsubscribe/:token/',
                component: () => import("@/views/Unsubscribe.vue"),
            },
            {
                // `<id>-<slug>`: the id resolves the product, the slug is decoration. The hyphen
                // in front of the decoration is required, mirroring ProductSlugConverter in
                // storefront/urls.py, where a looser pattern hands `12abc` to int() and 500s.
                // The bare id is an alias rather than an optional group: vue-router counts the
                // parentheses of a param pattern itself, so `(?:...)` inside one fails to compile.
                name: 'product',
                path: ':country/:type/:productSlug(\\d+-[-a-zA-Z0-9_]*)/',
                alias: ':country/:type/:productSlug(\\d+)/',
                component: () => import("@/views/Product.vue"),
            },
            {
                // A single segment is an owner-written page (content.Page); reserved roots are
                // blocked on the model, mirroring storefront/urls.py.
                name: 'page',
                path: ':pageSlug([a-z0-9][-a-z0-9_]*)/',
                component: () => import("@/views/Page.vue"),
            },
            {
                // Django 301s this to the language root (storefront/views.py), so a client-side
                // navigation has to land on the same address instead of rendering the home
                // listing under a second, non-canonical one. The query rides along - it may
                // carry an active `?q=`.
                path: 'all/all/',
                redirect: to => ({name: 'home', params: {lang: to.params.lang}, query: to.query}),
            },
            {
                // `all` means "any" on either segment; the canonical form of all/all is the home page.
                name: 'catalog',
                path: ':country/:type/',
                components: {
                    default: () => import("@/views/Catalog.vue"),
                    hero: () => import("@/components/storefront/HomeHero.vue"),
                },
            },
        ],
    },
    {
        // The server 302s `/` by Accept-Language before the SPA ever loads; this covers
        // client-side navigation to the bare root.
        path: '/',
        redirect: () => `/${useSettingsStore().currentLanguage || 'en'}/`,
    },
    {
        path: '/:pathMatch(.*)*',
        component: () => import("@/views/PageNotFound.vue"),
    },
];

const router = createRouter({
    history: createWebHistory(),
    routes: routes,
    // A new page starts at its top; back and forward return to where the reader was. Paging
    // inside the catalog is the exception - Catalog.vue scrolls to the grid itself, under the
    // fixed header - so a route that only changed its query is left alone.
    scrollBehavior(to, from, savedPosition) {
        if (savedPosition) return savedPosition;
        if (to.path === from.path) return false;
        return {top: 0};
    },
});

// The path prefix is the single source of the interface language.
router.beforeEach(async (to) => {
    const lang = to.params.lang;
    if (lang && SUPPORT_LOCALES.includes(lang)) {
        const settingsStore = useSettingsStore();
        if (settingsStore.currentLanguage !== lang) await settingsStore.setLanguage(lang);
    }
});

export default router;
