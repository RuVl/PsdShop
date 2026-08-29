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
                component: () => import("@/views/Catalog.vue"),
                meta: {name: 'routes.main'},
            },
            {
                name: 'cart',
                path: 'cart/',
                component: () => import("@/views/Cart.vue"),
                meta: {parent: 'home', name: 'routes.cart'},
            },
            {
                name: 'purchases',
                path: 'purchases/',
                component: () => import("@/views/MyPurchases.vue"),
                meta: {parent: 'home', name: 'routes.my_purchases'},
            },
            {
                // The token is the whole authentication - it arrives by e-mail and expires, see ADR-0002.
                name: 'purchases-list',
                path: 'purchases/:token/',
                component: () => import("@/views/Purchases.vue"),
                meta: {parent: 'home', name: 'routes.my_purchases'},
            },
            {
                // Reached from an e-mail footer; the token is signed, so the page needs nothing else.
                name: 'unsubscribe',
                path: 'unsubscribe/:token/',
                component: () => import("@/views/Unsubscribe.vue"),
                meta: {parent: 'home', name: 'routes.unsubscribe'},
            },
            {
                // `<id>-<slug>`: the id resolves the product, the slug is decoration.
                name: 'product',
                path: ':country/:type/:productSlug(\\d+[-a-zA-Z0-9_]*)/',
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
                // `all` means "any" on either segment; the canonical form of all/all is the home page.
                name: 'catalog',
                path: ':country/:type/',
                component: () => import("@/views/Catalog.vue"),
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
