<script setup>
import {computed} from 'vue';
import {useRoute} from 'vue-router';
import {SUPPORT_LOCALES} from '@/i18n/index.js';

// A flag linking to the current page in the other language - the language is the first path
// segment, mirroring Django's i18n_patterns. Inline SVG: flag emoji are blank on Windows.
const route = useRoute();

const other = computed(() => SUPPORT_LOCALES.find(code => code !== route.params.lang) || 'en');
const target = computed(() => route.fullPath.replace(/^\/(en|ru)(?=\/|$)/, `/${other.value}`));
const label = computed(() => (other.value === 'ru' ? 'Russian' : 'English'));
</script>

<template>
  <router-link class="lang opacity" :to="target" :title="label" :aria-label="label">
    <svg v-if="other === 'ru'" class="lang__flag" viewBox="0 0 9 6" preserveAspectRatio="xMidYMid slice"
         role="img" aria-hidden="true">
      <rect width="9" height="6" fill="#fff"/>
      <rect width="9" height="4" y="2" fill="#0039A6"/>
      <rect width="9" height="2" y="4" fill="#D52B1E"/>
    </svg>
    <svg v-else class="lang__flag" viewBox="0 0 60 30" preserveAspectRatio="xMidYMid slice" role="img"
         aria-hidden="true">
      <clipPath id="lang-gb-clip">
        <path d="M0,0 v30 h60 v-30 z"/>
      </clipPath>
      <g clip-path="url(#lang-gb-clip)">
        <path d="M0,0 v30 h60 v-30 z" fill="#012169"/>
        <path d="M0,0 L60,30 M60,0 L0,30" stroke="#fff" stroke-width="6"/>
        <path d="M30,0 v30 M0,15 h60" stroke="#fff" stroke-width="10"/>
        <path d="M30,0 v30 M0,15 h60" stroke="#C8102E" stroke-width="6"/>
      </g>
    </svg>
  </router-link>
</template>

<style scoped>
/* One box for both flags. Their proportions differ (3:2 against 2:1), so fitting them into it
   would leave the British one narrower - `slice` crops instead, the way object-fit: cover does.
   The width is the design's own (.lang__img). */
.lang__flag {
  display: block;
  width: 25px;
  height: 17px;
  border-radius: 2px;
}
</style>
