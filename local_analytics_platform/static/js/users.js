export function createUsersLoader({
  fetchJson,
  state,
  userPeriodParams,
  getUserGroupParams,
  getUserProfileParams,
  renderUsers,
}) {
  return async function loadUsers(days) {
    const period = userPeriodParams();
    const [users, userGroups, userProfiles] = await Promise.all([
      fetchJson("/api/user-analytics", { ...period, days: period.days || days, limit: 12 }),
      fetchJson("/api/user-analytics/groups", getUserGroupParams()),
      fetchJson("/api/user-analytics/users", getUserProfileParams()),
    ]);
    state.users = users;
    state.userGroups = userGroups;
    state.userProfiles = userProfiles;
    renderUsers();
  };
}
