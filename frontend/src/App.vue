<script setup>
import {computed, ref} from 'vue';
import {useRoute} from 'vue-router';
import LangSwitch from '@/components/storefront/LangSwitch.vue';
import FloatingCart from '@/components/storefront/FloatingCart.vue';
import HeroHeader from '@/components/storefront/HeroHeader.vue';
import {useContentStore} from '@/stores/content.js';
import {useLocalized} from '@/composables/localized.js';

// The design's shell: header with menu and language flag, the page, footer, floating cart.
// Markup and classes follow design/index.html (the storefront style.css is linked globally).
// The menu pages and the footer texts come from the content API - same rows the bot pages render.
const route = useRoute();
const contentStore = useContentStore();
const localized = useLocalized();
contentStore.load();

const lang = computed(() => route.params.lang || 'en');
const home = computed(() => ({name: 'home', params: {lang: lang.value}}));
// The hero lives on the listing pages; everywhere else the dark strip stays bare.
const showHero = computed(() => ['home', 'catalog'].includes(route.name));

const menuOpen = ref(false);

function toggleMenu() {
    menuOpen.value = !menuOpen.value;
    document.body.classList.toggle('lock', menuOpen.value);
}

function closeMenu() {
    menuOpen.value = false;
    document.body.classList.remove('lock');
}
</script>

<template>
  <header class="header" :class="{'header-active': menuOpen}">
    <div class="container">
      <div class="header__body">
        <router-link :to="home" class="logo opacity" @click="closeMenu">
          <picture class="logo__img"><img src="/static/storefront/img/icons/logo.png" alt="Logo icon"></picture>
        </router-link>
        <div class="header__block">
          <ul class="menu">
            <li class="menu__item white link-primary" @click="closeMenu">
              <router-link :to="home">{{ $t('storefront.nav.home') }}</router-link>
            </li>
            <li v-for="navPage in contentStore.pages" :key="navPage.slug" class="menu__item white link-primary"
                @click="closeMenu">
              <router-link :to="{name: 'page', params: {lang, pageSlug: navPage.slug}}">{{ localized(navPage, 'title') }}</router-link>
            </li>
          </ul>
          <LangSwitch/>
        </div>
        <div class="header__mobile">
          <LangSwitch/>
          <button type="button" class="btn-reset burger" :class="{'burger-active': menuOpen}" @click="toggleMenu">
            <span class="burger-icon"></span>
          </button>
        </div>
      </div>
    </div>
  </header>

  <HeroHeader :show-hero="showHero"/>

  <router-view/>

  <footer class="footer" id="footer">
    <div class="container">
      <div class="footer__body">
        <div class="footer__block">
          <router-link :to="home" class="logo opacity">
            <picture class="logo__img"><img src="/static/storefront/img/icons/logo-footer.png" alt="Logo icon"></picture>
          </router-link>
          <p v-if="contentStore.settings && localized(contentStore.settings, 'footer_note')" class="text-small black">
            {{ localized(contentStore.settings, 'footer_note') }}
          </p>
        </div>
        <div class="footer__block">
          <div class="footer__title title black upper">{{ $t('storefront.footer.links') }}</div>
          <div class="footer__menu">
            <ul class="footer__list">
              <li class="footer__item text black link-primary">
                <router-link :to="home">{{ $t('storefront.nav.home') }}</router-link>
              </li>
              <li v-for="navPage in contentStore.pages" :key="navPage.slug" class="footer__item text black link-primary">
                <router-link :to="{name: 'page', params: {lang, pageSlug: navPage.slug}}">{{ localized(navPage, 'title') }}</router-link>
              </li>
            </ul>
          </div>
        </div>
        <div class="footer__block">
          <a v-if="contentStore.settings?.support_url" class="btn btn-grade btn-big text white opacity"
             :href="contentStore.settings.support_url" target="_blank" rel="noopener">{{ $t('buttons.support') }}</a>
        </div>
      </div>
    </div>
  </footer>

  <FloatingCart/>
</template>
