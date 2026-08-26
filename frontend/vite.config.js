import {fileURLToPath, URL} from 'node:url'
import {defineConfig, loadEnv} from 'vite'
import vue from '@vitejs/plugin-vue'

// The storefront is server-rendered by Django; vite builds only the interactive "islands" and
// writes them, with fixed (unhashed) names, straight into the backend's static tree. Cache-busting
// is Django's job: {% static %} rewrites to the hashed name on collectstatic (ManifestStaticFiles).
// In development run `npm run build -- --watch`.
export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), '');

    return {
        define: {
            __API_URL__: JSON.stringify(env.VITE_API_URL)
        },
        // Islands only - do not copy frontend/public/ into the backend static tree.
        publicDir: false,
        plugins: [
            vue(),
        ],
        resolve: {
            alias: {
                '@': fileURLToPath(new URL('./src', import.meta.url))
            }
        },
        build: {
            outDir: '../backend/storefront/static/storefront/js',
            emptyOutDir: false,
            rollupOptions: {
                input: {
                    'cart-counter': fileURLToPath(new URL('./src/islands/cart-counter.js', import.meta.url)),
                },
                output: {
                    entryFileNames: '[name].js',
                    chunkFileNames: '[name].js',
                    assetFileNames: '[name][extname]',
                },
            },
        },
    }
})
