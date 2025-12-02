# Frontend Testing

This directory contains tests for the Immigreat frontend application.

## Test Structure

- `src/**/*.test.{ts,tsx}` - Component and service tests
- `src/test/setup.ts` - Global test setup and mocks
- `src/test/utils.tsx` - Test utilities and helpers

## Running Tests

```bash
# Run tests in watch mode
npm test

# Run tests with coverage
npm run test:coverage

# Run tests with UI
npm run test:ui
```

## Coverage Goals

- Overall: 90%+
- Branches: 90%+
- Functions: 90%+
- Lines: 90%+

## Test Categories

### Unit Tests

- `api.test.ts` - API service layer tests
- Component-specific tests

### Integration Tests

- `App.test.tsx` - Full application integration tests
- User interaction flows
- State management

## Mocking Strategy

- API calls mocked using Vitest's `vi.mock()`
- DOM APIs (IntersectionObserver, ResizeObserver) mocked in setup
- localStorage/sessionStorage cleared between tests

## Best Practices

1. Use `userEvent` for user interactions (not `fireEvent`)
2. Query by role and accessible labels when possible
3. Use `waitFor` for async operations
4. Clean up after each test (automatic via setup)
5. Test user behavior, not implementation details
