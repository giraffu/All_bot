const $ = (selector) => document.querySelector(selector);

export function createTabController({
  state,
  tabs,
  disposeChartsForTab,
  syncDaysControl,
  renderLastUpdated,
  loadCurrentTab,
}) {
  function setActiveTab(tabName, syncHash = true, shouldLoad = true) {
    const requested = tabName === "overview" ? "generation" : tabName;
    const tab = tabs[requested] ? requested : "users";
    const previousTab = state.activeTab;
    if (previousTab && previousTab !== tab) {
      disposeChartsForTab(previousTab);
    }
    state.activeTab = tab;
    document.querySelectorAll(".tab-button").forEach((button) => {
      button.classList.toggle("active", button.dataset.tab === tab);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.classList.toggle("active", panel.dataset.panel === tab);
    });
    $("#activeKicker").textContent = tabs[tab].kicker;
    $("#activeTitle").textContent = tabs[tab].title;
    $("#activeSubtitle").textContent = tabs[tab].subtitle;
    syncDaysControl();
    renderLastUpdated();
    if (syncHash || tabName === "overview") {
      history.replaceState(null, "", `#${tab}`);
    }
    if (shouldLoad) {
      loadCurrentTab();
    }
  }

  return { setActiveTab };
}
