<script setup>
import {computed, ref} from 'vue';
import {useRoute} from 'vue-router';
import LangSwitch from '@/components/storefront/LangSwitch.vue';
import FloatingCart from '@/components/storefront/FloatingCart.vue';

// The design's shell: header with menu and language flag, the page, footer, floating cart.
// Markup and classes follow design/index.html (the storefront style.css is linked globally).
const route = useRoute();
const lang = computed(() => route.params.lang || 'en');
const home = computed(() => ({name: 'home', params: {lang: lang.value}}));

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
            <li class="menu__item white link-primary" @click="closeMenu"><a href="#">{{ $t('storefront.nav.rules') }}</a></li>
            <li class="menu__item white link-primary" @click="closeMenu"><a href="#">{{ $t('storefront.nav.contacts') }}</a></li>
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

  <router-view/>

  <footer class="footer" id="footer">
    <div class="container">
      <div class="footer__body">
        <div class="footer__block">
          <router-link :to="home" class="logo opacity">
            <picture class="logo__img"><img src="/static/storefront/img/icons/logo-footer.png" alt="Logo icon"></picture>
          </router-link>
        </div>
        <div class="footer__block">
          <div class="footer__title title black upper">{{ $t('storefront.footer.links') }}</div>
          <div class="footer__menu">
            <ul class="footer__list">
              <li class="footer__item text black link-primary">
                <router-link :to="home">{{ $t('storefront.nav.home') }}</router-link>
              </li>
              <li class="footer__item text black link-primary"><a href="#">{{ $t('storefront.nav.contacts') }}</a></li>
              <li class="footer__item text black link-primary"><a href="#">{{ $t('storefront.nav.rules') }}</a></li>
            </ul>
          </div>
        </div>
        <div class="footer__block"></div>
      </div>
    </div>
  </footer>

  <FloatingCart/>
</template>
