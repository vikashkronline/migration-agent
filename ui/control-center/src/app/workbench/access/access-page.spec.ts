import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';
import { AccessApi } from './access-api';
import { AccessPage } from './access-page';
import type { AccessDecision, AccessPolicy, AccessReview } from './access.models';

const digest = 'sha256:' + 'a'.repeat(64);
const policy: AccessPolicy = {
  schema_version: 2,
  git_repository: null,
  catalog_version: 1,
  revision: 1,
  revision_nonce: 'a'.repeat(32),
  previous_digest: null,
  binding: {
    project_id: 'fixture',
    source_root: 'C:/source',
    governance_root: 'C:/governance',
    source_root_commit: 'a'.repeat(40),
    governance_root_commit: 'b'.repeat(40),
  },
  roles: [{ role_id: 'viewer', label: 'Viewer', capabilities: ['project.read'] }],
  members: [
    {
      principal_id: 'owner',
      label: 'Owner',
      roles: ['viewer'],
      status: 'active',
      os_identity: 'test:owner',
      public_key: null,
      key_fingerprint: null,
      git_account: null,
      expires_at: null,
    },
  ],
  owners: ['owner'],
  rules: {},
};
function session(capabilities: readonly string[]): AccessDecision {
  return {
    allowed: true,
    reason: 'ALLOWED',
    principal_id: 'owner',
    roles: ['viewer'],
    capabilities,
    access_digest: digest,
  };
}
function api(capabilities: readonly string[]) {
  const review: AccessReview = {
    proposal: {
      proposal_id: 'b'.repeat(32),
      candidate: policy,
      snapshot_digest: digest,
      revision_locator: 'rev-' + 'a'.repeat(16),
      base_digest: digest,
      proposer: 'test:owner',
      created_at: 1,
      expires_at: 900,
      nonce: 'c'.repeat(32),
    },
    before: policy,
    signing_digest: digest,
    approval_channel: 'trusted-terminal',
    review_command: [
      'agent',
      'access',
      'approve',
      'C:/source',
      'b'.repeat(32),
      '--state-dir',
      'C:/state',
    ],
    message: 'Trusted terminal required',
  };
  return {
    session: vi.fn(() => of(session(capabilities))),
    policy: vi.fn(() => of(policy)),
    catalog: vi.fn(() => of(['project.read'])),
    propose: vi.fn(() => of(review)),
    directory: vi.fn(),
  };
}

describe('Owner user management', () => {
  it('shows a viewer their permissions without administrative forms', async () => {
    const service = api(['project.read', 'access.read']);
    TestBed.configureTestingModule({ providers: [{ provide: AccessApi, useValue: service }] });
    const fixture = TestBed.createComponent(AccessPage);
    await fixture.whenStable();
    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('My access');
    expect(root.querySelector('form')).toBeNull();
    expect(service.propose).not.toHaveBeenCalled();
    fixture.destroy();
  });

  it('prepares an exact member proposal and presents a terminal handoff', async () => {
    const service = api(['project.read', 'access.read', 'access.propose']);
    TestBed.configureTestingModule({ providers: [{ provide: AccessApi, useValue: service }] });
    const fixture = TestBed.createComponent(AccessPage);
    await fixture.whenStable();
    const root = fixture.nativeElement as HTMLElement;
    const form = root.querySelector('form');
    if (!form) throw new Error('Member form missing');
    const principal = form.querySelector<HTMLInputElement>('[name=principal_id]');
    const label = form.querySelector<HTMLInputElement>('[name=label]');
    const role = form.querySelector<HTMLInputElement>('[name=role]');
    if (!principal || !label || !role) throw new Error('Member fields missing');
    principal.value = 'new-member';
    label.value = 'New member';
    role.checked = true;
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await fixture.whenStable();
    expect(service.propose).toHaveBeenCalledWith(digest, [
      {
        kind: 'member.set',
        member: {
          principal_id: 'new-member',
          label: 'New member',
          roles: ['viewer'],
          status: 'pending',
          os_identity: null,
          public_key: null,
          key_fingerprint: null,
          git_account: null,
          expires_at: null,
        },
      },
    ]);
    expect(root.querySelector<HTMLTextAreaElement>('#approval-command')?.value).toContain(
      "'agent' 'access' 'approve'",
    );
    expect(root.textContent).toContain('Current policy');
    expect(root.textContent).toContain('Proposed policy');
    fixture.destroy();
  });

  it('keeps pending Git membership separate from provider maintainer labels', async () => {
    const service = api(['project.read', 'access.read']);
    service.policy.mockReturnValue(
      of({
        ...policy,
        members: [
          {
            ...policy.members[0]!,
            status: 'pending',
            os_identity: null,
            git_account: {
              provider: 'gitlab',
              host: 'gitlab.com',
              account_id: '42',
              login: '<script>untrusted</script>',
            },
          },
        ],
      }),
    );
    TestBed.configureTestingModule({ providers: [{ provide: AccessApi, useValue: service }] });
    const fixture = TestBed.createComponent(AccessPage);
    await fixture.whenStable();
    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('pending');
    expect(root.querySelector('script')).toBeNull();
    fixture.destroy();
  });
});
