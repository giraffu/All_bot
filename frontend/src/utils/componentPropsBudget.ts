export function warnIfPropsExceedBudget(
  componentName: string,
  propCount: number,
  budget = 10,
) {
  if (!import.meta.env.DEV) {
    return
  }
  if (propCount <= budget) {
    return
  }
  console.warn(
    `[props-budget] ${componentName} exposes ${propCount} props, exceeding budget ${budget}. Consider grouping props or extracting child components.`,
  )
}
