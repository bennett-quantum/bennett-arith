//! Independent certificate replay through the gate-pinned ISA reader API.
use bennett_isa_ref::{ClaimVerdict, Object, QinplaceApplicability};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    assert_eq!(args.len(), 3, "expected object path and claim count");
    let text = std::fs::read_to_string(&args[1]).expect("read publication");
    let object = Object::parse(&text).expect("admit raw publication");
    let reports = object.verify_certificate().expect("replay certificate claims");
    let expected: usize = args[2].parse().expect("integer claim count");
    assert!(expected > 0, "publication must contain certificate claims");
    assert_eq!(reports.claims.len(), expected, "every stored claim must be replayed");
    for (closure, applicability) in &reports.qinplace_applicability {
        assert!(matches!(applicability, QinplaceApplicability::Established),
                "publication {}: unestablished qinplace applicability for {closure}: {applicability:?}", args[1]);
    }
    for report in reports.claims {
        assert!(matches!(report.verdict, ClaimVerdict::Proof | ClaimVerdict::Evidence { .. }),
                "publication {}: rejected or unverified claim: {report:?}", args[1]);
    }
}
