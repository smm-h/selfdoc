package svelte

import (
	"regexp"
	"strings"
)

// prop is one property a component accepts.
type prop struct {
	// Name is the property name as the component destructures it.
	Name string
	// Type is the declared type, empty when the component declares none.
	Type string
	// Default is the default value as written. A rest element carries the
	// literal "...rest" here, which is how the Python marks it.
	Default string
	// Bindable reports whether the property was declared with $bindable().
	Bindable bool
}

var (
	// propsCall matches the destructuring of the $props() rune, with its
	// optional type annotation.
	propsCall = regexp.MustCompile(
		`(?s)(?:let|const)` + pySpace + `+\{([^}]*)\}(?:` + pySpace + `*:` + pySpace +
			`*(.+?))?` + pySpace + `*=` + pySpace + `*\$props\(\)`)

	// bindableCall matches a $bindable() default, capturing the value inside.
	bindableCall = regexp.MustCompile(`^\$bindable\((.*)\)$`)

	// typeMemberSeparator splits an inline object type into its members.
	typeMemberSeparator = regexp.MustCompile(`[;,]`)

	// legacyProp matches an "export let" property declaration, which is how
	// Svelte 3 and 4 components declare their properties.
	legacyProp = regexp.MustCompile(
		`export` + pySpace + `+let` + pySpace + `+(` + pyWord + `+)(?:` + pySpace + `*:` +
			pySpace + `*([^=;]+?))?(?:` + pySpace + `*=` + pySpace + `*([^;]+?))?` +
			pySpace + `*;`)
)

// extractProps reads the properties a Svelte 5 component declares through the
// $props() rune.
//
// The type of each property comes from the annotation on the destructuring: an
// inline object type gives each property its own type, and a named interface
// is reported as the type of every property, because the interface's own
// declaration is not in this file to read.
func extractProps(scriptContent string) []prop {
	match := propsCall.FindStringSubmatch(scriptContent)
	if match == nil {
		return nil
	}

	destructureContent := match[1]
	typeAnnotation := pyStrip(match[2])

	propTypes := map[string]string{}
	interfaceName := ""
	if typeAnnotation != "" {
		if strings.HasPrefix(typeAnnotation, "{") && strings.HasSuffix(typeAnnotation, "}") {
			inner := typeAnnotation[1 : len(typeAnnotation)-1]
			for _, part := range typeMemberSeparator.Split(inner, -1) {
				part = pyStrip(part)
				if part == "" {
					continue
				}
				if colonIdx := strings.Index(part, ":"); colonIdx > 0 {
					name := strings.TrimLeft(pyStrip(part[:colonIdx]), "?")
					propTypes[name] = pyStrip(part[colonIdx+1:])
				}
			}
		} else {
			interfaceName = typeAnnotation
		}
	}

	var props []prop
	for _, item := range splitDestructure(destructureContent) {
		item = pyStrip(item)
		if item == "" {
			continue
		}

		if strings.HasPrefix(item, "...") {
			props = append(props, prop{
				Name:    pyStrip(item[3:]),
				Default: "...rest",
			})
			continue
		}

		name, defaultValue, bindable := parsePropItem(item)

		propType := propTypes[name]
		if propType == "" && interfaceName != "" {
			propType = interfaceName
		}

		props = append(props, prop{
			Name:     name,
			Type:     propType,
			Default:  defaultValue,
			Bindable: bindable,
		})
	}

	return props
}

// splitDestructure splits destructuring content on the commas at nesting depth
// zero, so a default value's own commas stay with their property.
func splitDestructure(content string) []string {
	var items []string
	depth := 0
	var current strings.Builder

	for _, ch := range content {
		switch ch {
		case '(', '{', '[':
			depth++
			current.WriteRune(ch)
		case ')', '}', ']':
			depth--
			current.WriteRune(ch)
		case ',':
			if depth == 0 {
				items = append(items, current.String())
				current.Reset()
			} else {
				current.WriteRune(ch)
			}
		default:
			current.WriteRune(ch)
		}
	}

	if current.Len() > 0 {
		items = append(items, current.String())
	}

	return items
}

// parsePropItem splits one destructured property into its name, its default
// value and whether it is bindable. A $bindable() default reports the value
// inside the call as the default, since that is what the property defaults to.
func parsePropItem(item string) (name, defaultValue string, bindable bool) {
	eqIdx := -1
	depth := 0
	for i := 0; i < len(item); i++ {
		switch item[i] {
		case '(', '{', '[':
			depth++
		case ')', '}', ']':
			depth--
		case '=':
			if depth == 0 {
				eqIdx = i
			}
		}
		if eqIdx >= 0 {
			break
		}
	}

	if eqIdx < 0 {
		return pyStrip(item), "", false
	}

	name = pyStrip(item[:eqIdx])
	defaultRaw := pyStrip(item[eqIdx+1:])

	if m := bindableCall.FindStringSubmatch(defaultRaw); m != nil {
		return name, pyStrip(m[1]), true
	}

	return name, defaultRaw, false
}

// extractLegacyProps reads the properties a Svelte 3 or 4 component declares
// with "export let". Such a property is never reported as bindable: every one
// of them can be bound, so the column would say the same thing for all of
// them, and the Python this ports reports them all as not bindable.
func extractLegacyProps(scriptContent string) []prop {
	var props []prop
	for _, match := range legacyProp.FindAllStringSubmatch(scriptContent, -1) {
		props = append(props, prop{
			Name:    match[1],
			Type:    pyStrip(match[2]),
			Default: pyStrip(match[3]),
		})
	}
	return props
}
