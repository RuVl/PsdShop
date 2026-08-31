<script setup>
import {computed} from 'vue';
import {useRoute} from 'vue-router';
import {useSettingsStore} from '@/stores/settings.js';
import PageDecor from '@/components/storefront/PageDecor.vue';

// The catch-all route: it also matches addresses with no language prefix, so the way home is the
// language the visitor is browsing in rather than the one in the (missing) path.
const route = useRoute();
const settings = useSettingsStore();

const lang = computed(() => route.params.lang || settings.currentLanguage || 'en');
</script>

<template>
  <PageDecor/>

  <main class="main-content">
    <section class="shop mb-100">
      <div class="container">
        <h1 class="title-section black">404</h1>
        <p class="text black not-found__text">{{ $t('other.page_not_found') }}</p>
        <router-link class="button" :to="{name: 'home', params: {lang}}">{{ $t('buttons.go_back_home') }}</router-link>
      </div>
    </section>
  </main>
</template>

<style scoped>
.not-found__text {
  margin: 20px 0 25px;
  max-width: 640px;
}
</style>
