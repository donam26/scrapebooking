// Mỗi namespace một tệp JSON. Thêm namespace: tạo tệp ở mọi ngôn ngữ + thêm một dòng ở đây (xem docs/i18n.md).
import type { Messages } from "..";

import common from "./common.json";
import format from "./format.json";
import labels from "./labels.json";
import errors from "./errors.json";
import shell from "./shell.json";
import components from "./components.json";
import helpers from "./helpers.json";
import landing from "./landing.json";
import auth from "./auth.json";
import today from "./today.json";
import overview from "./overview.json";
import marketTab from "./marketTab.json";
import calendar from "./calendar.json";
import pace from "./pace.json";
import competitors from "./competitors.json";
import market from "./market.json";
import hotels from "./hotels.json";
import events from "./events.json";
import insights from "./insights.json";
import settings from "./settings.json";
import admin from "./admin.json";
import runs from "./runs.json";
import radar from "./radar.json";
import otb from "./otb.json";
import rms from "./rms.json";
import reputation from "./reputation.json";
import setup from "./setup.json";
import reports from "./reports.json";

const messages: Messages = {
  common,
  format,
  labels,
  errors,
  shell,
  components,
  helpers,
  landing,
  auth,
  today,
  overview,
  marketTab,
  calendar,
  pace,
  competitors,
  market,
  hotels,
  events,
  insights,
  settings,
  admin,
  runs,
  radar,
  otb,
  rms,
  reputation,
  setup,
  reports,
};

export default messages;
