import {mkdirSync, readFileSync, writeFileSync} from 'node:fs'
import {transform} from 'lightningcss'

mkdirSync('/backend/storefront/static/storefront/css', {recursive: true})

// shop.css/style.css ship straight from the backend static tree, linked by both presentations
// (docs/architecture.md) - not bundled by vite, so no build step touches them normally. Minifying
// them in place on disk would overwrite the readable, git-tracked source the next time someone
// runs `make spa` locally, so this only runs inside the Docker build (backend/Dockerfile), reading
// from a throwaway copy and writing into the image alone.
for (const name of ['style.css', 'shop.css']) {
    const {code} = transform({
        filename: name,
        code: readFileSync(`/tmp/raw-css/${name}`),
        minify: true,
    })
    writeFileSync(`/backend/storefront/static/storefront/css/${name}`, code)
}
