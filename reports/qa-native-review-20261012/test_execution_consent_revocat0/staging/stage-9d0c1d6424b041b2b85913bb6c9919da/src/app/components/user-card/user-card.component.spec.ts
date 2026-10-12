import { ComponentFixture, TestBed } from '@angular/core/testing';
import { UserCardComponent } from './user-card.component';

describe('UserCardComponent', () => {
  let component: UserCardComponent;
  let fixture: ComponentFixture<UserCardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [UserCardComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(UserCardComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create and toggle local state', () => {
    expect(component).toBeTruthy();
    expect(component.isExpanded()).toBe(false);
    component.toggleDetails();
    expect(component.isExpanded()).toBe(true);
  });
});
