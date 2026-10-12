import type { NodePage, WorkDetail, WorkNode } from './workbench.models';

export const projectFixture: WorkNode = {
  node_id: 'project',
  parent_id: null,
  label: 'Fixture project',
  kind: 'project',
  status: 'UNKNOWN',
  status_tone: 'neutral',
  dependencies: [],
  child_count: 0,
  complete_count: 0,
  task_count: 2,
  run_id: null,
  needs_attention: false,
};
export const taskFixture: WorkNode = {
  ...projectFixture,
  node_id: 'task-a',
  label: 'Review interfaces',
  kind: 'task',
  status: 'APPROVAL_RECORDED',
  status_tone: 'info',
  task_count: 0,
  run_id: 'run-1',
};
export const pageFixture: NodePage = {
  schema_version: 1,
  project_id: 'bound',
  revision: 'r1',
  cursor: 1,
  nodes: [projectFixture],
  ancestors: [],
  total: 1,
  next_offset: null,
};

export function detailFixture(node: WorkNode = taskFixture): WorkDetail {
  return {
    schema_version: 1,
    project_id: 'bound',
    revision: 'r1',
    node,
    summary: 'Exact recorded task evidence',
    run_id: node.kind === 'task' ? 'run-1' : null,
    changeset_id: node.kind === 'task' ? 'cs-1' : null,
    changeset_digest: node.kind === 'task' ? 'digest-1' : null,
    base_revision: 'base',
    policy_digest: 'policy',
    validation_digest: 'validation',
    evidence: [['BUILD', 'PASSED']],
    files: ['src/example.ts'],
    diff: '<img src=x onerror=alert(1)>',
    review_command: ['agent', 'approve', 'step-1'],
    ask_command: ['agent', 'ask', '--entity', node.node_id],
    actions:
      node.kind === 'task'
        ? [
            {
              kind: 'apply',
              label: 'Apply approved exact artifact',
              available: true,
              reason: 'Exact core preflight required',
            },
          ]
        : [],
    activity: [],
    diagram: '',
    images: [],
    milestones: [['Plan', 'RECORDED']],
  };
}
