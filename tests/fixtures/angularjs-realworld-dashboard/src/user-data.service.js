angular.module('dashboardApp')
  .service('UserDataService', function($http) {
    this.getUsers = function() {
      return $http.get('/api/v1/users');
    };

    this.updateStatus = function(userId, status) {
      return $http.post('/api/v1/users/' + userId + '/status', { status: status });
    };
  });
