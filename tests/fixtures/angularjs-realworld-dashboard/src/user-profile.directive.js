angular.module('dashboardApp', [])
  .directive('userProfile', function() {
    return {
      restrict: 'E',
      scope: {
        name: '@',
        role: '@',
        department: '@'
      },
      templateUrl: 'user-profile.template.html',
      controller: function($scope) {
        $scope.isExpanded = false;

        $scope.toggleDetails = function() {
          $scope.isExpanded = !$scope.isExpanded;
        };
      },
      link: function(scope, element, attrs) {
        // Direct DOM manipulation in legacy directive
      }
    };
  });
