from . import test_fqns

# Expose the list of tests for parallel execution in make
if __name__ == '__main__':
    print('\n'.join(test_fqns()))
