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
    },
})

export default defineConfig(({mode}) => {
    const env = loadEnv(mode, process.cwd(), '');

    return {
        define: {
            // Same-origin /api in production (one domain); dev overrides via .env.development.
            __API_URL__: JSON.stringify(env.VITE_API_URL || process.env.VITE_API_URL || '/api')
        },
        base: '/static/storefront/spa/',
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
