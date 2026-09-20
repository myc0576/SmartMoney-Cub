#!/usr/bin/env node
'use strict';

/**
 * SmartMoney-Cub DSH Stdio Sidecar Plugin
 *
 * Implements the smartmoney_cub_dsh_stdio.v1 protocol over stdin/stdout.
 * Strictly enforces the smartmoney-review profile and safety declaration:
 * READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE.
 *
 * Supported capabilities:
 * - review_envelope
 * - review_events
 * - review_cancel
 * - review_resume
 * - review_fork
 * - review_close
 * - heartbeat
 *
 * Forbidden capabilities (fail-closed):
 * - shell, filesystem, network, web, jobs, workflow, subagent,
 *   agent-team, broker, order, trade, account, order_cancel
 */

const readline = require('node:readline');

const DSH_PROTOCOL = 'smartmoney_cub_dsh_stdio.v1';
const DSH_PROFILE = 'smartmoney-review';
const SAFETY_DECLARATION = 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE';

const ALLOWED_CAPABILITIES = [
  'review_envelope',
  'review_events',
  'review_cancel',
  'review_resume',
  'review_fork',
  'review_close',
  'heartbeat'
];

const FORBIDDEN_CAPABILITIES = [
  'shell',
  'filesystem',
  'network',
  'web',
  'jobs',
  'workflow',
  'subagent',
  'agent-team',
  'broker',
  'order',
  'trade',
  'account',
  'order_cancel'
];

class DshPluginSession {
  constructor() {
    this.connected = false;
    this.profile = null;
    this.envelope = null;
    this.subscriptions = new Set();
    this.reviews = new Map();
  }

  handleRequest(req) {
    if (!req || typeof req !== 'object') {
      return this.errorResponse(null, -32600, 'Invalid Request');
    }
    const id = req.id !== undefined ? req.id : null;
    const method = req.method;
    const params = req.params || {};

    switch (method) {
      case 'handshake':
        return this.handleHandshake(id, params);
      case 'heartbeat':
        return this.handleHeartbeat(id, params);
      case 'subscribe':
        return this.handleSubscribe(id, params);
      case 'cancel':
        return this.handleCancel(id, params);
      case 'resume':
        return this.handleResume(id, params);
      case 'fork':
        return this.handleFork(id, params);
      case 'close':
        return this.handleClose(id, params);
      case 'teardown':
      case 'shutdown':
        return this.handleTeardown(id, params);
      default:
        return this.errorResponse(id, -32601, 'Method not allowed or unsupported in review profile');
    }
  }

  handleHandshake(id, params) {
    const protocol = params.protocol;
    const profile = params.profile || {};
    const envelope = params.envelope;

    if (protocol !== DSH_PROTOCOL) {
      return this.errorResponse(id, 'invalid_protocol', 'Unsupported protocol version');
    }
    if (profile.name !== DSH_PROFILE) {
      return this.errorResponse(id, 'invalid_profile', 'Only smartmoney-review profile allowed');
    }
    if (profile.safety !== SAFETY_DECLARATION) {
      return this.errorResponse(id, 'invalid_safety', 'Invalid safety declaration');
    }
    if (profile.allow_network || profile.allow_shell || profile.allow_filesystem || profile.allow_credentials) {
      return this.errorResponse(id, 'forbidden_capability', 'Profile must remain local and restricted');
    }
    if (!envelope || !envelope.review_id || !envelope.payload) {
      return this.errorResponse(id, 'invalid_review_envelope', 'Valid redacted review envelope required');
    }

    this.connected = true;
    this.profile = profile;
    this.envelope = envelope;
    this.reviews.set(envelope.review_id, {
      status: 'active',
      seq: 0,
      envelope: envelope
    });

    return this.successResponse(id, {
      accepted: true,
      protocol: DSH_PROTOCOL,
      profile: DSH_PROFILE,
      capabilities: ALLOWED_CAPABILITIES,
      safety: SAFETY_DECLARATION
    });
  }

  handleHeartbeat(id) {
    return this.successResponse(id, {
      alive: true,
      connected: this.connected,
      active_reviews: this.reviews.size,
      safety: SAFETY_DECLARATION
    });
  }

  handleSubscribe(id, params) {
    if (!this.connected) {
      return this.errorResponse(id, 'not_connected', 'Handshake required prior to subscription');
    }
    const topics = Array.isArray(params.topics) ? params.topics : [];
    for (const t of topics) {
      this.subscriptions.add(t);
    }
    return this.successResponse(id, {
      subscribed: Array.from(this.subscriptions).sort(),
      safety: SAFETY_DECLARATION
    });
  }

  handleCancel(id, params) {
    if (!this.connected) {
      return this.errorResponse(id, 'not_connected', 'Handshake required');
    }
    const reviewId = params.review_id;
    if (this.reviews.has(reviewId)) {
      this.reviews.get(reviewId).status = 'cancelled';
    }
    return this.successResponse(id, {
      review_id: reviewId,
      status: 'cancelled',
      safety: SAFETY_DECLARATION
    });
  }

  handleResume(id, params) {
    if (!this.connected) {
      return this.errorResponse(id, 'not_connected', 'Handshake required');
    }
    const reviewId = params.review_id;
    const afterSeq = params.after_seq || 0;
    if (this.reviews.has(reviewId)) {
      this.reviews.get(reviewId).status = 'active';
      this.reviews.get(reviewId).seq = Math.max(this.reviews.get(reviewId).seq, afterSeq);
    }
    return this.successResponse(id, {
      review_id: reviewId,
      status: 'active',
      resumed_after_seq: afterSeq,
      safety: SAFETY_DECLARATION
    });
  }

  handleFork(id, params) {
    if (!this.connected) {
      return this.errorResponse(id, 'not_connected', 'Handshake required');
    }
    const sourceId = params.review_id;
    const title = params.title || '';
    const forkId = sourceId + '-fork-' + Date.now();
    this.reviews.set(forkId, {
      status: 'active',
      seq: 0,
      title: title,
      forked_from: sourceId
    });
    return this.successResponse(id, {
      fork_review_id: forkId,
      source_review_id: sourceId,
      title: title,
      safety: SAFETY_DECLARATION
    });
  }

  handleClose(id, params) {
    if (!this.connected) {
      return this.errorResponse(id, 'not_connected', 'Handshake required');
    }
    const reviewId = params.review_id;
    if (this.reviews.has(reviewId)) {
      this.reviews.delete(reviewId);
    }
    return this.successResponse(id, {
      review_id: reviewId,
      closed: true,
      safety: SAFETY_DECLARATION
    });
  }

  handleTeardown(id) {
    this.connected = false;
    this.reviews.clear();
    this.subscriptions.clear();
    const res = this.successResponse(id, {
      teardown: true,
      safety: SAFETY_DECLARATION
    });
    setImmediate(() => process.exit(0));
    return res;
  }

  successResponse(id, result) {
    return {
      jsonrpc: '2.0',
      id: id,
      result: result,
      safety: SAFETY_DECLARATION
    };
  }

  errorResponse(id, code, message) {
    return {
      jsonrpc: '2.0',
      id: id,
      error: {
        code: typeof code === 'number' ? code : -32000,
        name: String(code),
        message: message
      },
      safety: SAFETY_DECLARATION
    };
  }
}

function main() {
  const session = new DshPluginSession();
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
  });

  rl.on('line', (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    try {
      const req = JSON.parse(trimmed);
      const resp = session.handleRequest(req);
      process.stdout.write(JSON.stringify(resp) + '\n');
    } catch (err) {
      const errResp = {
        jsonrpc: '2.0',
        id: null,
        error: {
          code: -32700,
          message: 'Parse error'
        },
        safety: SAFETY_DECLARATION
      };
      process.stdout.write(JSON.stringify(errResp) + '\n');
    }
  });

  process.on('SIGTERM', () => {
    session.handleTeardown(null);
  });
  process.on('SIGINT', () => {
    session.handleTeardown(null);
  });
}

if (require.main === module) {
  main();
}

module.exports = {
  DSH_PROTOCOL,
  DSH_PROFILE,
  SAFETY_DECLARATION,
  ALLOWED_CAPABILITIES,
  FORBIDDEN_CAPABILITIES,
  DshPluginSession
};

