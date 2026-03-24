rm -rf snapshots/ storage/

cov_path=cov_noint/$1


mkdir -p $cov_path


mv default_* $cov_path/
cd $cov_path
grcov . -s ../../ --binary-path ../../target/release/ --llvm-path $(dirname $(find $(rustc --print target-libdir)/../bin -name llvm-profdata))  --branch --ignore-not-existing --ignore "/*" -t lcov  -o .


lcov --summary lcov
cd -
