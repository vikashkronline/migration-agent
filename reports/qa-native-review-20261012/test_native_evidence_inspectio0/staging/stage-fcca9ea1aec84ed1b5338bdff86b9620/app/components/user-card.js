import Component from '@ember/component';

export default Component.extend({
  isExpanded: false,

  actions: {
    toggleDetails() {
      this.toggleProperty('isExpanded');
    },
  },
});

