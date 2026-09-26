import { Component, OnInit, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';

@Component({
  selector: 'app-user-card',
  standalone: true,
  templateUrl: './user-card.component.html',
  styleUrls: ['./user-card.component.css']
})
export class UserCardComponent implements OnInit {
  private http = inject(HttpClient);
  users = signal<any[]>([]);

  ngOnInit(): void {
    this.http.get('/api/users').subscribe((data: any) => {
      this.users.set(data);
    });
  }
}
