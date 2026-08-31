<script setup>
// The hero the listing pages put inside the dark strip, straight from design/index.html - the SPA
// half of the `hero` block storefront/catalog.html overrides.
import {useContentStore} from '@/stores/content.js';

// The design puts a support button under the copy; without it the strip ends in a tall empty block
// on a phone. The address is the owner's own (content.SiteSettings), so the button only appears
// once they have filled it in - the design's second link (reviews) has no source behind it and is
// left out rather than faked.
const contentStore = useContentStore();
</script>

<template>
  <section class="home" id="home">
    <div class="container">
      <div class="home__body">
        <div class="home__block">
          <h1 class="home__title title white">{{ $t('storefront.hero.title') }}</h1>
          <p class="home__text text white">{{ $t('storefront.hero.text') }}</p>
          <div v-if="contentStore.settings?.support_url" class="home__btns">
            <a class="btn btn-big btn-grade text white opacity" :href="contentStore.settings.support_url"
               target="_blank" rel="noopener">{{ $t('buttons.support') }}</a>
          </div>
        </div>
        <picture class="home__img">
          <!-- Its own size: below 880px the picture is in the flow, and without it the strip
               grows under the reader the moment it loads. -->
          <img src="/static/storefront/img/home/home-img.png" alt="Decor" width="734" height="650">
        </picture>
      </div>
    </div>
  </section>
</template>
