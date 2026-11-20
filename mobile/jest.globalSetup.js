// Every test runs in the developer's time zone, which is behind UTC. A calendar date read as
// UTC midnight then shows as the day before, so that bug fails tests on any machine and in CI.
module.exports = () => {
  process.env.TZ = 'America/Indiana/Indianapolis';
};
