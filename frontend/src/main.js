import './assets/main.css'

import {createApp} from 'vue'
import App from '@/App.vue'
import router from "@/router/index.js";
import pinia from "@/stores/index.js";
import {setupI18n} from '@/i18n/index.js';
import {useSettingsStore} from "@/stores/settings.js";

const app = createApp(App);

// Pinia first: vue-router starts the initial navigation from its own install(), and the
// root redirect reads the language out of a store - with the router registered first that
// resolution runs before there is an active pinia.
app.use(pinia);
app.use(router);

const settingsStore = useSettingsStore();
const i18n = await setupI18n({locale: settingsStore.currentLanguage});
app.use(i18n);

app.mount('#app');
