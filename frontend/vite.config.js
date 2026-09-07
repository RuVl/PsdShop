import {fileURLToPath, URL} from 'node:url'
import {existsSync, mkdirSync, renameSync} from 'node:fs'
import {defineConfig, loadEnv} from 'vite'
import vue from '@vitejs/plugin-vue'

// Dynamic rendering: humans get this SPA, search bots get Django-rendered HTML on the same
// URLs. Vite bundles the SPA with hashed asset names into the backend static tree, and the
// built index.html becomes the Django "shell" template: the build injects {{ ... }} hooks the
// shell view fills with per-page meta, then moves the file into the backend templates dir.
// `npm run dev` serves the untouched index.html - the hooks exist only in the build output.

const OUT_DIR = '../backend/storefront/static/storefront/spa'
const SHELL_TEMPLATE = '../backend/storefront/templates/storefront/shell.html'
const CSS_DIR = '../backend/storefront/static/storefront/css'
// Raw source for both - style.css is the designer's file (CLAUDE.md: kept a copy of the mockup),
// shop.css is ours. Neither is imported from SPA source, so they need their own rollup input to
// get minified; the fixed output name below is what lets them stay at their existing /static/...
// URL (base.html, shell.html and this file's own <link> tags never change).
const RAW_CSS = {style: 'style.css', shop: 'shop.css'}

const djangoShell = () => ({
    name: 'django-shell',
    apply: 'build',
    transformIndexHtml(html) {
        return html
            .replace('<html lang="en">', '<html lang="{{ LANGUAGE_CODE }}">')
            // The meta builder renders <title> too, so the static one is replaced whole.
            .replace(/<title>.*?<\/title>/, '{{ storefront_meta }}')
    },
    closeBundle() {
        const shell = fileURLToPath(new URL(SHELL_TEMPLATE, import.meta.url))
        const built = fileURLToPath(new URL(`${OUT_DIR}/index.html`, import.meta.url))
        if (existsSync(built)) {
            mkdirSync(fileURLToPath(new URL('.', new URL(SHELL_TEMPLATE, import.meta.url))), {recursive: true})
            renameSync(built, shell)
        }

        const cssDir = fileURLToPath(new URL(CSS_DIR, import.meta.url))
        mkdirSync(cssDir, {recursive: true})
        for (const name of Object.values(RAW_CSS)) {
            const minified = fileURLToPath(new URL(`${OUT_DIR}/raw-css/${name}`, import.meta.url))
            if (existsSync(minified)) {
                renameSync(minified, fileURLToPath(new URL(`${CSS_DIR}/${name}`, import.meta.url)))
            }
        }
    },
})

export default defineConfig(({mode}) => {
    const env = loadEnv(mode, process.cwd(), '');

    return {
        define: {
            // One domain, so the built SPA always talks to the same-origin /api - a build must
            // never bake in a host. The dev server takes VITE_API_URL (.env.development).
            __API_URL__: JSON.stringify(mode === 'development' ? (env.VITE_API_URL || 'http://localhost:8000/api') : '/api')
        },
        // Production puts the SPA in the backend static tree, so its assets are addressed
        // from there. The dev server must stay on the root instead: a base under /static would
        // be swallowed by the proxy below, which sends every /static request to Django.
        base: mode === 'production' ? '/static/storefront/spa/' : '/',
        plugins: [
            // Design images are absolute /static/... URLs served by the backend - leave them
            // alone instead of trying to bundle them.
            vue({template: {transformAssetUrls: false}}),
            djangoShell(),
        ],
        resolve: {
            alias: {
                '@': fileURLToPath(new URL('./src', import.meta.url))
            }
        },
        build: {
            outDir: OUT_DIR,
            emptyOutDir: true,
            rollupOptions: {
                input: {
                    main: fileURLToPath(new URL('./index.html', import.meta.url)),
                    ...Object.fromEntries(
                        Object.entries(RAW_CSS).map(([key, name]) => [key, fileURLToPath(new URL(`${CSS_DIR}/${name}`, import.meta.url))]),
                    ),
                },
                output: {
                    // Keep the SPA's own chunks/assets on the normal hashed pattern; only the two
                    // raw CSS entries get a fixed name, picked up by name (see RAW_CSS above).
                    assetFileNames: (assetInfo) => {
                        const rawName = Object.values(RAW_CSS).find((name) => assetInfo.names?.includes(name))
                        return rawName ? `raw-css/${rawName}` : 'assets/[name]-[hash][extname]'
                    },
                },
            },
        },
        server: {
            // The SPA references the same /static and /media the backend serves (design CSS,
            // images, previews) - in dev those come from the host Django on :8000.
            proxy: {
                '/static': env.VITE_BACKEND_URL || 'http://localhost:8000',
                '/media': env.VITE_BACKEND_URL || 'http://localhost:8000',
            },
        },
    }
})
