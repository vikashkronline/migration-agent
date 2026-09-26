angular.module('dashboardApp')
  .component('activityFeed', {
    bindings: {
      title: '@',
      limit: '<'
    },
    templateUrl: 'activity-feed.template.html',
    controller: function() {
      var ctrl = this;
      ctrl.isExpanded = false;

      ctrl.toggleFeed = function() {
        ctrl.isExpanded = !ctrl.isExpanded;
      };
    }
  });
