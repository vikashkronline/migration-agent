angular.module('app').directive('userBadge', function() {
  return {
    restrict: 'E',
    scope: {
      name: '@',
      role: '@',
    },
    templateUrl: 'src/user-badge.template.html',
    link: function(scope) {
      scope.isExpanded = false;
      scope.toggleDetails = function() {
        scope.isExpanded = !scope.isExpanded;
      };
    },
  };
});
