import { ComponentFixture, TestBed } from '@angular/core/testing';

import { HrpanelComponent } from './hrpanel.component';

describe('HrpanelComponent', () => {
  let component: HrpanelComponent;
  let fixture: ComponentFixture<HrpanelComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HrpanelComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(HrpanelComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
