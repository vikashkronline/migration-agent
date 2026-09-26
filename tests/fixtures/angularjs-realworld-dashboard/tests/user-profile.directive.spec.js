describe('userProfile directive', function() {
  var $compile, $rootScope;

  beforeEach(module('dashboardApp'));

  beforeEach(inject(function(_$compile_, _$rootScope_) {
    $compile = _$compile_;
    $rootScope = _$rootScope_;
  }));

  it('renders user name and toggles profile', function() {
    var scope = $rootScope.$new();
    scope.testName = 'Alice Developer';
    var element = $compile('<user-profile name="{{testName}}" role="Engineer" department="Platform"></user-profile>')(scope);
    scope.$digest();
    expect(element.html()).toContain('Alice Developer');
  });
});
