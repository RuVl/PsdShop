<script setup>
import {ref, watch} from 'vue';
import {useRoute} from 'vue-router';
import {fetchPage} from '@/api/content.js';
import {useLocalized} from '@/composables/localized.js';

// An owner-written text page (content.Page) - the SPA presentation of /:lang/<slug>/.
const route = useRoute();
const localized = useLocalized();

const page = ref(null);
const state = ref('loading');

async function load() {
    state.value = 'loading';
    try {
        page.value = await fetchPage(route.params.pageSlug);
        state.value = 'ready';
    } catch (error) {
        state.value = error.response?.status === 404 ? 'not_found' : 'failed';
    }
}

watch(() => route.params.pageSlug, load, {immediate: true});
</script>

<template>
  <main class="main-content">
    <section class="mb-60">
      <div class="container">
        <p v-if="state === 'loading'" class="text black">{{ $t('products.loading') }}</p>
        <p v-else-if="state === 'not_found'" class="text black">{{ $t('storefront.grid.not_found') }}</p>
        <p v-else-if="state === 'failed'" class="text black">{{ $t('errors.unavailable') }}</p>
        <template v-else>
          <h1 class="title-section title black">{{ localized(page, 'title') }}</h1>
          <!-- Owner-authored HTML from the admin editor. -->
          <div class="idesc" v-html="localized(page, 'body')"></div>
        </template>
      </div>
    </section>
  </main>
</template>
