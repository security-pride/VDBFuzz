set -x

export GOCOVERDIR="coverage_data"

cov_path=cov_fvdb_noint/$1
mkdir -p $cov_path
mkdir -p $cov_path/coverage_data


mv $GOCOVERDIR/* $cov_path/coverage_data/


cd $cov_path
go tool covdata textfmt -i=coverage_data -o=coverage.txt

TOTAL_LINES=$(wc -l < coverage.txt | tr -d ' ')

COVERED_LINES=$(grep -v ' 0$' coverage.txt | wc -l | tr -d ' ')

echo "(Covered statement blocks): $COVERED_LINES"


cd -
rm -rf data

