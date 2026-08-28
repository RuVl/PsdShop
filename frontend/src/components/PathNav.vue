<script setup>
import {useRouter} from "vue-router";

const router = useRouter();
const route_chain = [];

// Walk meta.parent up to the root. Params (the /:lang prefix) ride along, and a route without
// meta.name simply draws no breadcrumb instead of feeding $t an undefined key.
for (let route = router.currentRoute.value; route?.meta?.name;) {
  route_chain.unshift(route);
  const parent = route.meta.parent;
  if (!parent || !router.hasRoute(parent)) break;
  route = router.resolve({name: parent, params: router.currentRoute.value.params});
}
</script>

<template>
  <nav v-if="route_chain" class="path-nav">
    <span v-for="route in route_chain">
      <router-link :to="route">{{ $t(route.meta.name) }}</router-link>
    </span>
  </nav>
</template>

<style lang="scss" scoped>
.path-nav {
  font-size: 12px;
  color: var(--second-color-text);

  & > span:not(:last-child)::after {
    margin: 0 10px;
    content: '/';
  }

  a {
    text-decoration: none;
    color: inherit;

    &:hover {
      opacity: .7;
    }
  }
}
</style>