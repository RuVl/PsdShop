<script setup>
import Block from "@/components/Block.vue";
import PathNav from "@/components/PathNav.vue";
</script>

<template>
  <Block class="view-block">
    <PathNav class="path-nav"/>
    <h2 class="title">
      <slot name="title"/>
    </h2>
    <slot/>
  </Block>
</template>

<style lang="scss" scoped>
.view-block {
  /* The Verdoc-era pages centered themselves via #app; that lives here now. */
  width: 100%;
  max-width: 1200px;
  margin-left: auto;
  margin-right: auto;

  & > .title {
    margin: 20px 0;
  }
}

@media only screen and (max-width: 480px) {
  .view-block {
    > .path-nav, > .title {
      text-align: center;
    }
  }
}
</style>